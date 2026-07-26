"""Plan 249 F5 — las GL* llegan al panel por el endpoint de lint que YA existe. 6 tests.

PREREQUISITO de todos: `STACKY_DEVOPS_PIPELINE_LINT_ENABLED` (gate PREEXISTENTE de la ruta,
api/devops.py) tiene que estar ON o la ruta devuelve 404 por una razon ajena a este plan.
"""
from __future__ import annotations

import pytest

GL_EVIDENCIA = """\
stages: [build, deploy]
.base:
  image: mvn:3
build:
  stage: build
  extends: .base
  needs: [deploy]
  script: [mvn package]
deploy:
  stage: deploy
  environment: production
  script: [./deploy.sh]
ghost:
  stage: nonexistent
  script: [echo hi]
"""

RUTA = "/api/devops/pipeline-lint/validate"


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    """Se setea sobre la INSTANCIA `config.config`, nunca sobre el modulo."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_PIPELINE_LINT_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_GITLAB_SEMANTIC_RULES_ENABLED", True, raising=False)
    yield


def _post(app, body):
    return app.test_client().post(RUTA, json=body)


def test_flag_on_agrega_semantic_findings(app):
    body = _post(app, {"source": "gitlab", "yaml": GL_EVIDENCIA}).get_json()
    codigos = {f["code"] for f in body["semantic_findings"]}
    assert {"GL001", "GL002", "GL005"} <= codigos


def test_flag_off_respuesta_identica(app, monkeypatch):
    import config as cfg

    con_flag = _post(app, {"source": "gitlab", "yaml": GL_EVIDENCIA}).get_json()
    monkeypatch.setattr(cfg.config, "STACKY_GITLAB_SEMANTIC_RULES_ENABLED", False, raising=False)
    sin_flag = _post(app, {"source": "gitlab", "yaml": GL_EVIDENCIA}).get_json()
    assert "semantic_findings" not in sin_flag
    con_flag.pop("semantic_findings", None)
    for clave in ("ok", "findings", "counts", "engine_version", "fixes_omitted"):
        assert sin_flag.get(clave) == con_flag.get(clave), clave


def test_source_ado_no_cambia(app, monkeypatch):
    import config as cfg

    ado = "steps:\n- script: echo hola\n"
    assert "semantic_findings" not in _post(app, {"source": "ado", "yaml": ado}).get_json()
    monkeypatch.setattr(cfg.config, "STACKY_GITLAB_SEMANTIC_RULES_ENABLED", False, raising=False)
    assert "semantic_findings" not in _post(app, {"source": "ado", "yaml": ado}).get_json()


def test_flag_se_lee_de_la_instancia(app, monkeypatch):
    """GOTCHA DURA: parchear el MODULO devolveria el default y el branch OFF no correria."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_GITLAB_SEMANTIC_RULES_ENABLED", False, raising=False)
    assert "semantic_findings" not in _post(app, {"source": "gitlab", "yaml": GL_EVIDENCIA}).get_json()
    monkeypatch.setattr(cfg.config, "STACKY_GITLAB_SEMANTIC_RULES_ENABLED", True, raising=False)
    assert "semantic_findings" in _post(app, {"source": "gitlab", "yaml": GL_EVIDENCIA}).get_json()


def test_known_runner_tags_opcional(app):
    yaml_tags = "stages: [build]\nb:\n  stage: build\n  tags: [windows]\n  script: [make]\n"
    sin = _post(app, {"source": "gitlab", "yaml": yaml_tags}).get_json()
    assert not [f for f in sin["semantic_findings"] if f["code"] == "GL007"]
    con = _post(app, {"source": "gitlab", "yaml": yaml_tags,
                      "known_runner_tags": ["docker"]}).get_json()
    assert len([f for f in con["semantic_findings"] if f["code"] == "GL007"]) == 1


def test_404_si_el_lint_esta_apagado(app, monkeypatch):
    """Gate PREEXISTENTE: documentado para que nadie lo confunda con una regresion."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_PIPELINE_LINT_ENABLED", False, raising=False)
    assert _post(app, {"source": "gitlab", "yaml": GL_EVIDENCIA}).status_code == 404
